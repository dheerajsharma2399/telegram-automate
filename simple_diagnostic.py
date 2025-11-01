#!/usr/bin/env python3
"""
Email Generation Diagnostic Test
Identifies why some jobs are not getting email bodies generated
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import Database
from llm_processor import LLMProcessor

def load_environment():
    """Load environment variables for database connection"""
    try:
        # Load from .env file if exists
        env_file = project_root / '.env'
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip().strip('"\'')
        
        return os.getenv('DATABASE_URL') or os.getenv('SUPABASE_URL') or 'sqlite:///jobs.db'
    except Exception as e:
        print(f"Error loading environment: {e}")
        return 'sqlite:///jobs.db'

def analyze_email_generation_issues():
    """Analyze why some jobs are not getting email bodies"""
    
    print("EMAIL GENERATION DIAGNOSTIC TEST")
    print("=" * 50)
    
    # Initialize database
    try:
        db_url = load_environment()
        print(f"Database URL: {db_url}")
        db = Database(db_url)
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Database initialization failed: {e}")
        return
    
    print("\nDATABASE ANALYSIS")
    print("=" * 30)
    
    # Get all processed jobs
    print("\n1. Getting all processed jobs...")
    all_jobs = []
    
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM processed_jobs ORDER BY created_at DESC LIMIT 20")
            all_jobs = [dict(r) for r in cur.fetchall()]
        
        print(f"Found {len(all_jobs)} recent jobs in database")
        
    except Exception as e:
        print(f"Query failed: {e}")
        return
    
    if not all_jobs:
        print("No jobs found in database")
        return
    
    # Categorize jobs by email status
    print("\n2. Categorizing jobs by email status...")
    
    email_jobs_missing_body = []
    email_jobs_with_body = []
    non_email_jobs = []
    
    for job in all_jobs:
        has_email = job.get('email') and str(job.get('email')).strip()
        has_body = job.get('email_body') and str(job.get('email_body')).strip()
        
        if has_email and not has_body:
            email_jobs_missing_body.append(job)
        elif has_email and has_body:
            email_jobs_with_body.append(job)
        else:
            non_email_jobs.append(job)
    
    print(f"Jobs with email, missing body: {len(email_jobs_missing_body)}")
    print(f"Jobs with email, with body: {len(email_jobs_with_body)}")
    print(f"Jobs without email: {len(non_email_jobs)}")
    
    # Analyze jobs that should have email bodies
    print("\n3. Analyzing jobs that SHOULD have email bodies...")
    
    if email_jobs_missing_body:
        print(f"Found {len(email_jobs_missing_body)} jobs that should have email bodies:")
        
        for i, job in enumerate(email_jobs_missing_body[:3], 1):
            job_id = job.get('job_id', 'N/A')
            company = job.get('company_name', 'N/A')
            role = job.get('job_role', 'N/A')
            email = job.get('email', 'N/A')
            
            print(f"\n   [{i}] Job ID: {job_id}")
            print(f"       Company: {company}")
            print(f"       Role: {role}")
            print(f"       Email: {email}")
    
    # Test the database method
    print("\n4. Testing get_email_jobs_needing_generation method...")
    
    try:
        method_results = db.get_email_jobs_needing_generation()
        print(f"Method returned {len(method_results)} jobs needing email generation")
        
        if method_results:
            print("Database method is working correctly")
        else:
            print("WARNING: Database method returned 0 results")
            print("This could mean:")
            print("- All email jobs already have bodies")
            print("- Database query condition is too restrictive")
            print("- No jobs meet the criteria")
            
    except Exception as e:
        print(f"Database method failed: {e}")
    
    # Summary
    print("\n" + "="*50)
    print("SUMMARY & RECOMMENDATIONS")
    print("="*50)
    
    if email_jobs_missing_body:
        print(f"\nPROBLEM IDENTIFIED: {len(email_jobs_missing_body)} jobs need email bodies")
        print("\nRecommended actions:")
        print("1. Check if user_profile.json exists")
        print("2. Verify email generation function works")
        print("3. Run /generate_emails command manually")
        print("4. Check logs for generation errors")
    else:
        print("\nNo issues found - all email jobs have bodies!")

if __name__ == "__main__":
    analyze_email_generation_issues()