-- ==========================================
-- MIGRATE NON-EMAIL JOBS TO DASHBOARD
-- ==========================================
-- This query will populate dashboard_jobs table with existing non-email jobs
-- from the processed_jobs table

INSERT INTO dashboard_jobs (
    source_job_id,
    original_sheet,
    company_name,
    job_role,
    location,
    application_link,
    phone,
    recruiter_name,
    job_relevance,
    original_created_at,
    application_status,
    application_date,
    notes,
    is_duplicate,
    duplicate_of_id,
    conflict_status,
    created_at,
    updated_at
)
SELECT
    pj.job_id as source_job_id,
    'non-email' as original_sheet,
    pj.company_name,
    pj.job_role,
    pj.location,
    pj.application_link,
    NULL as phone,
    NULL as recruiter_name,
    'relevant' as job_relevance,
    pj.created_at as original_created_at,
    'not_applied' as application_status,
    NULL as application_date,
    NULL as notes,
    FALSE as is_duplicate,
    NULL as duplicate_of_id,
    'none' as conflict_status,
    CURRENT_TIMESTAMP as created_at,
    CURRENT_TIMESTAMP as updated_at
FROM processed_jobs pj
LEFT JOIN dashboard_jobs dj ON pj.job_id = dj.source_job_id
WHERE dj.source_job_id IS NULL  -- Only jobs not already in dashboard
AND (pj.email IS NULL OR pj.email = '')  -- Only non-email jobs
AND pj.is_hidden = FALSE;  -- Only visible jobs

-- Check how many jobs were migrated
SELECT 
    'Jobs Migrated' as description,
    COUNT(*) as count
FROM dashboard_jobs 
WHERE original_sheet = 'non-email';

-- Show current dashboard job count
SELECT 
    'Total Dashboard Jobs' as description,
    COUNT(*) as count
FROM dashboard_jobs;