#!/usr/bin/env python3
"""
PostgreSQL-compatible database wrapper for Telegram Job Scraper
Fixes the "cannot convert dictionary update sequence element" error
"""
import os
import logging
from contextlib import contextmanager
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

class Database:
    def __init__(self, db_path_or_url: str):
        self.db_path_or_url = db_path_or_url
        self.logger = logging.getLogger(__name__)
        
        # Parse PostgreSQL connection string or use SQLite fallback
        self.is_postgresql = db_path_or_url.startswith('postgresql://') or db_path_or_url.startswith('postgres://')
        
        if self.is_postgresql:
            self._setup_postgresql()
        else:
            self._setup_sqlite()
            
        self.init_database()
    
    def _setup_postgresql(self):
        """Setup PostgreSQL connection pool"""
        try:
            self.pool = ThreadedConnectionPool(
                1, 20, 
                self.db_path_or_url,
                cursor_factory=RealDictCursor
            )
            self.logger.info("PostgreSQL connection pool created")
        except Exception as e:
            self.logger.error(f"Failed to setup PostgreSQL pool: {e}")
            raise
    
    def _setup_sqlite(self):
        """Setup SQLite fallback"""
        import sqlite3
        self.is_postgresql = False
        self.conn_class = sqlite3
        self.row_class = sqlite3.Row
        self.logger.info("Using SQLite fallback")
    
    @contextmanager
    def get_connection(self):
        """Get database connection with proper row handling"""
        if self.is_postgresql:
            conn = self.pool.getconn()
            conn.autocommit = True
            try:
                yield conn
            finally:
                self.pool.putconn(conn)
        else:
            import sqlite3
            conn = sqlite3.connect(self.db_path_or_url, timeout=10)
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if self.is_postgresql:
                # Raw messages table (PostgreSQL)
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
                
                # Processed jobs table (PostgreSQL)
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
                
                # Bot config table (PostgreSQL)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_config (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Commands queue table (PostgreSQL)
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
                
                # Initialize default config
                cursor.execute("""
                    INSERT INTO bot_config (key, value) VALUES
                    ('monitoring_status', 'stopped'),
                    ('last_processed_message_id', '0'),
                    ('total_messages_processed', '0'),
                    ('total_jobs_extracted', '0')
                    ON CONFLICT (key) DO NOTHING
                """)
                
            else:
                # SQLite fallback - simplified version
                cursor.execute("""
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
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_config (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
    
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
        """Get unprocessed messages - Fixed for PostgreSQL"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM raw_messages 
                WHERE status = 'unprocessed'
                ORDER BY created_at ASC
                LIMIT %s
            """, (limit,))
            
            # Return as list of dictionaries
            return [dict(row) for row in cursor.fetchall()]
    
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
    
    def get_pending_commands(self, limit: int = 10) -> List[Dict]:
        """Retrieve pending commands for the bot to execute."""
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
    
    def get_unprocessed_count(self) -> int:
        """Get count of unprocessed messages"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM raw_messages WHERE status = 'unprocessed'")
            result = cursor.fetchone()
            return result['count'] if result else 0
    
    # Add other methods as needed...
