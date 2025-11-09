-- ===============================================
-- TELEGRAM JOB SCRAPER - SUPABASE TABLE SETUP
-- PostgreSQL Database Initialization Script
-- ===============================================

-- Create raw_messages table for storing Telegram messages
CREATE TABLE IF NOT EXISTS raw_messages (
    id SERIAL PRIMARY KEY,
    message_id INTEGER UNIQUE NOT NULL,
    message_text TEXT NOT NULL,
    sender_id INTEGER,
    sent_at TIMESTAMP,
    status TEXT DEFAULT 'unprocessed',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create processed_jobs table for parsed job postings
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
);

-- Create bot_config table for configuration storage
CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create commands_queue table for dashboard-to-bot communication
CREATE TABLE IF NOT EXISTS commands_queue (
    id SERIAL PRIMARY KEY,
    command TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP NULL,
    status TEXT DEFAULT 'pending',
    result_text TEXT,
    executed_by TEXT
);

-- Create telegram_auth table for Telegram session storage
CREATE TABLE IF NOT EXISTS telegram_auth (
    id SERIAL PRIMARY KEY,
    session_string TEXT,
    login_status TEXT DEFAULT 'not_authenticated',
    phone_number TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===============================================
-- INITIAL DEFAULT DATA
-- ===============================================

-- Initialize default bot configuration
INSERT INTO bot_config (key, value) VALUES
    ('monitoring_status', 'stopped'),
    ('last_processed_message_id', '0'),
    ('total_messages_processed', '0'),
    ('total_jobs_extracted', '0')
ON CONFLICT (key) DO NOTHING;

-- Initialize Telegram authentication record
INSERT INTO telegram_auth (id, login_status) 
VALUES (1, 'not_authenticated')
ON CONFLICT (id) DO NOTHING;

-- ===============================================
-- INDEXES FOR PERFORMANCE
-- ===============================================

-- Index for faster message lookup by status
CREATE INDEX IF NOT EXISTS idx_raw_messages_status ON raw_messages(status);

-- Index for faster job lookup by company
CREATE INDEX IF NOT EXISTS idx_processed_jobs_company ON processed_jobs(company_name);

-- Index for faster job lookup by creation date
CREATE INDEX IF NOT EXISTS idx_processed_jobs_created_at ON processed_jobs(created_at);

-- Index for faster command queue lookup
CREATE INDEX IF NOT EXISTS idx_commands_queue_status ON commands_queue(status);

-- ===============================================
-- VERIFICATION QUERIES
-- ===============================================

-- ===============================================
-- DASHBOARD JOBS SYSTEM - NEW TABLES
-- ===============================================

-- Dashboard jobs table (isolated system for job management)
CREATE TABLE IF NOT EXISTS dashboard_jobs (
    id SERIAL PRIMARY KEY,
    source_job_id TEXT, -- Reference to original job ID
    original_sheet TEXT, -- 'email', 'non-email', 'email-exp', 'non-email-exp'
    company_name TEXT,
    job_role TEXT,
    location TEXT,
    application_link TEXT,
    phone TEXT,
    recruiter_name TEXT,
    job_relevance TEXT, -- 'relevant' or 'irrelevant'
    original_created_at TIMESTAMP,
    
    -- Dashboard-specific fields (DO NOT sync back)
    application_status TEXT DEFAULT 'not_applied', -- 'not_applied', 'applied', 'interview', 'rejected', 'offer', 'archived'
    application_date TIMESTAMP,
    notes TEXT,
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of_id INTEGER,
    conflict_status TEXT, -- 'none', 'detected', 'resolved'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Duplicate detection table
CREATE TABLE IF NOT EXISTS job_duplicate_groups (
    id SERIAL PRIMARY KEY,
    primary_job_id INTEGER, -- References dashboard_jobs.id
    duplicate_jobs TEXT[], -- Array of job IDs that are duplicates
    confidence_score DECIMAL(3,2), -- 0.00 to 1.00
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_status ON dashboard_jobs(application_status);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_company ON dashboard_jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_relevance ON dashboard_jobs(job_relevance);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_created ON dashboard_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_duplicate ON dashboard_jobs(is_duplicate);

-- =============================================--
-- VERIFICATION QUERIES (UPDATED)
-- =============================================--

-- Verify all tables were created (including new ones)
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('raw_messages', 'processed_jobs', 'bot_config', 'commands_queue', 'telegram_auth', 'dashboard_jobs', 'job_duplicate_groups')
ORDER BY table_name;

-- Check table structures (including new ones)
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
AND table_name IN ('raw_messages', 'processed_jobs', 'bot_config', 'commands_queue', 'telegram_auth', 'dashboard_jobs', 'job_duplicate_groups')
ORDER BY table_name, ordinal_position;