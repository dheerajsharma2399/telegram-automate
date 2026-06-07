-- ===============================================
-- TELEGRAM JOB SCRAPER - SUPABASE TABLE SETUP
-- PostgreSQL Database Initialization Script
-- Includes unified jobs + Phase 1 v2/v3 ingestion schema
-- ===============================================

-- Raw Telegram messages table
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
CREATE INDEX IF NOT EXISTS idx_raw_messages_status ON raw_messages(status);

-- Universal ingestion event log
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

-- Processing queue for raw_events workers
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

-- Unified jobs table
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

-- Phase 1 jobs extensions; ADD COLUMN keeps this script idempotent for existing installs
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS confidence_score FLOAT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS extraction_method TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_fingerprint TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS normalized_role TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS role_category TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS experience_hint TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS location_hint TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS contact_method TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS poster_name TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS poster_url TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS post_url TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_event_id INTEGER REFERENCES raw_events(id);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS apply_status TEXT DEFAULT 'pending';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS apply_run_id TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS recruiter_name TEXT;

-- Safe generated full-text search column migration
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jobs' AND column_name = 'search_vector'
          AND generation_expression IS NULL
    ) THEN
        EXECUTE 'DROP INDEX IF EXISTS idx_jobs_search';
        EXECUTE 'ALTER TABLE jobs DROP COLUMN search_vector';
    END IF;

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

CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company_name ON jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_jobs_job_relevance ON jobs(job_relevance);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_metadata_gin ON jobs USING gin(metadata);
CREATE INDEX IF NOT EXISTS idx_jobs_search ON jobs USING gin(search_vector);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(job_fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_normalized_role ON jobs(normalized_role);
CREATE INDEX IF NOT EXISTS idx_jobs_confidence ON jobs(confidence_score);

-- Apply runs table
CREATE TABLE IF NOT EXISTS apply_runs (
    run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    profile_used TEXT,
    status TEXT DEFAULT 'running',
    email_subject TEXT,
    email_body TEXT,
    approved_subject TEXT,
    approved_body TEXT,
    tokens_used INTEGER DEFAULT 0,
    model_used TEXT,
    error_message TEXT,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_apply_runs_job_id ON apply_runs(job_id);
CREATE INDEX IF NOT EXISTS idx_apply_runs_status ON apply_runs(status);

-- Legacy processed_jobs table retained for compatibility
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
CREATE INDEX IF NOT EXISTS idx_processed_jobs_company ON processed_jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_processed_jobs_created_at ON processed_jobs(created_at);

-- Configuration and command queue
CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS commands_queue (
    id SERIAL PRIMARY KEY,
    command TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP NULL,
    status TEXT DEFAULT 'pending',
    result_text TEXT,
    executed_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_commands_queue_status ON commands_queue(status);

-- Telegram session state
CREATE TABLE IF NOT EXISTS telegram_auth (
    id SERIAL PRIMARY KEY,
    session_string TEXT,
    login_status TEXT DEFAULT 'not_authenticated',
    phone_number TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Legacy dashboard tables retained for compatibility
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
    job_relevance TEXT,
    original_created_at TIMESTAMP,
    application_status TEXT DEFAULT 'not_applied',
    application_date TIMESTAMP,
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of_id INTEGER,
    conflict_status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_status ON dashboard_jobs(application_status);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_company ON dashboard_jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_relevance ON dashboard_jobs(job_relevance);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_created ON dashboard_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_duplicate ON dashboard_jobs(is_duplicate);

CREATE TABLE IF NOT EXISTS job_duplicate_groups (
    id SERIAL PRIMARY KEY,
    primary_job_id INTEGER,
    duplicate_jobs TEXT[],
    confidence_score DECIMAL(3,2),
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT
);

-- Initial default data
INSERT INTO bot_config (key, value) VALUES
    ('monitoring_status', 'stopped'),
    ('last_processed_message_id', '0'),
    ('total_messages_processed', '0'),
    ('total_jobs_extracted', '0')
ON CONFLICT (key) DO NOTHING;

INSERT INTO telegram_auth (id, login_status)
VALUES (1, 'not_authenticated')
ON CONFLICT (id) DO NOTHING;

-- Verification queries
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN (
    'raw_messages', 'raw_events', 'processing_queue', 'jobs', 'apply_runs',
    'processed_jobs', 'bot_config', 'commands_queue', 'telegram_auth',
    'dashboard_jobs', 'job_duplicate_groups'
)
ORDER BY table_name;

SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
AND table_name IN ('raw_events', 'processing_queue', 'jobs', 'apply_runs')
ORDER BY table_name, ordinal_position;
