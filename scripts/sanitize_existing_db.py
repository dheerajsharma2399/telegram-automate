import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent dir to path so we can import sanitizer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sanitizer import sanitize_job_record

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("Error: DATABASE_URL environment variable is not set.")
    sys.exit(1)

try:
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    with conn.cursor() as cursor:
        print("Fetching all jobs from database...")
        cursor.execute("SELECT * FROM jobs")
        jobs = cursor.fetchall()
        print(f"Loaded {len(jobs)} jobs. Beginning sanitization...")
        
        updated_count = 0
        for job in jobs:
            job_id = job['id']
            original_company = job['company_name']
            original_role = job['job_role']
            original_email = job['email']
            original_location = job['location']
            original_jd = job['jd_text']
            original_fingerprint = job['job_fingerprint']
            
            # Make a copy and sanitize
            sanitized = sanitize_job_record(dict(job))
            
            changed = (
                sanitized['company_name'] != original_company or
                sanitized['job_role'] != original_role or
                sanitized['email'] != original_email or
                sanitized['location'] != original_location or
                sanitized['jd_text'] != original_jd or
                sanitized['job_fingerprint'] != original_fingerprint
            )
            
            if changed:
                cursor.execute("""
                    UPDATE jobs
                    SET company_name = %s,
                        job_role = %s,
                        email = %s,
                        location = %s,
                        jd_text = %s,
                        job_fingerprint = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (
                    sanitized['company_name'],
                    sanitized['job_role'],
                    sanitized['email'],
                    sanitized['location'],
                    sanitized['jd_text'],
                    sanitized['job_fingerprint'],
                    job_id
                ))
                updated_count += 1
                
                print(f"Updated job ID {job_id}:")
                if sanitized['company_name'] != original_company:
                    print(f"  Company: {original_company!r} -> {sanitized['company_name']!r}")
                if sanitized['job_role'] != original_role:
                    print(f"  Role: {original_role!r} -> {sanitized['job_role']!r}")
                if sanitized['email'] != original_email:
                    print(f"  Email: {original_email!r} -> {sanitized['email']!r}")
                if sanitized['location'] != original_location:
                    print(f"  Location: {original_location!r} -> {sanitized['location']!r}")
                if sanitized['jd_text'] != original_jd:
                    # Print snippet of before/after for JD text
                    orig_len = len(original_jd or "")
                    new_len = len(sanitized['jd_text'] or "")
                    print(f"  JD Text: Cleaned (length {orig_len} -> {new_len})")
        
        if updated_count > 0:
            conn.commit()
            print(f"\nSuccessfully committed changes. Total jobs sanitized & updated: {updated_count}")
        else:
            print("\nNo jobs required updates. All records are already clean!")
            
except Exception as e:
    print(f"Error: {e}")
