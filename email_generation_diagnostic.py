
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Email Generation Diagnostic Test
Identifies why some jobs are not getting email bodies generated
"""

import os
import sys
import locale
import json
from datetime import datetime
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
    
    print("🔍 EMAIL GENERATION DIAGNOSTIC TEST")
    print("=" * 50)
    
    # Initialize database and LLM processor
    try:
        db_url = load_environment()
        print(f"📊 Database URL: {db_url}")
        
        db = Database(db_url)
        
        # Check if we have a user profile for email generation
        user_profile_path = project_root / 'user_profile.json'
        if user_profile_path.exists():
            print("✅ User profile found for email generation")
        else:
            print("❌ User profile NOT found - this may prevent email generation")
        
        # Initialize LLM processor for email generation test
        try:
            from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL
            llm_processor = LLMProcessor(
                OPENROUTER_API_KEY or "dummy_key",
                OPENROUTER_MODEL or "anthropic/claude-3.5-sonnet", 
                OPENROUTER_FALLBACK_MODEL or "openai/gpt-4o-mini"
            )
            print("✅ LLM processor initialized")
        except Exception as e:
            print(f"⚠️ LLM processor error: {e}")
            llm_processor = None
            
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return
    
    print("\n" + "="*50)
    print("📋 DATABASE ANALYSIS")
    print("="*50)
    
    # 1. Get all processed jobs
    print("\n1️⃣ Getting all processed jobs...")
    try:
        all_jobs = []
        
        # Try different methods to get jobs
        try:
            all_jobs = db.get_unsynced_jobs() or []
            print(f"✅ Found {len(all_jobs)} unsynced jobs")
        except:
            pass
            
        if not all_jobs:
            try:
                # Fallback: query directly
                with db.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM processed_jobs ORDER BY created_at DESC LIMIT 50")
                    all_jobs = [dict(r) for r in cur.fetchall()]
                print(f"✅ Found {len(all_jobs)} recent jobs (fallback query)")
            except Exception as e:
                print(f"❌ Query failed: {e}")
                all_jobs = []
                
    except Exception as e:
        print(f"❌ Failed to get jobs: {e}")
        all_jobs = []
    
    if not all_jobs:
        print("❌ No jobs found in database")
        return
    
    print(f"📊 Total jobs in database: {len(all_jobs)}")
    
    # 2. Categorize jobs by email status
    print("\n2️⃣ Categorizing jobs by email status...")
    
    categories = {
        'email_jobs_missing_body': [],
        'email_jobs_with_body': [],
        'non_email_jobs': [],
        'all_other_jobs': []
    }
    
    for job in all_jobs:
        has_email = job.get('email') and str(job.get('email')).strip()
        has_body = job.get('email_body') and str(job.get('email_body')).strip()
        
        if has_email and not has_body:
            categories['email_jobs_missing_body'].append(job)
        elif has_email and has_body:
            categories['email_jobs_with_body'].append(job)
        elif has_email:  # Shouldn't happen due to above, but just in case
            categories['email_jobs_missing_body'].append(job)
        else:
            categories['non_email_jobs'].append(job)
    
    print(f"📧 Jobs with email, missing body: {len(categories['email_jobs_missing_body'])}")
    print(f"📧 Jobs with email, with body: {len(categories['email_jobs_with_body'])}")
    print(f"🚫 Jobs without email: {len(categories['non_email_jobs'])}")
    
    # 3. Analyze jobs that should have email bodies
    print("\n3️⃣ Analyzing jobs that SHOULD have email bodies...")
    
    should_have_email_body = categories['email_jobs_missing_body']
    if should_have_email_body:
        print(f"🎯 Found {len(should_have_email_body)} jobs that should have email bodies:")
        
        for i, job in enumerate(should_have_email_body[:10], 1):  # Show first 10
            job_id = job.get('job_id', 'N/A')
            company = job.get('company_name', 'N/A')
            role = job.get('job_role', 'N/A')
            email = job.get('email', 'N/A')
            jd_text = job.get('jd_text', '')
            
            print(f"\n   [{i}] Job ID: {job_id}")
            print(f"       Company: {company}")
            print(f"       Role: {role}")
            print(f"       Email: {email}")
            print(f"       JD Length: {len(jd_text)} chars")
            print(f"       JD Preview: {jd_text[:100]}...")
            
            # Test email generation for this job
            if llm_processor:
                try:
                    print("       🔄 Testing email generation...")
                    test_body = llm_processor.generate_email_body(job, jd_text)
                    
                    if test_body and len(test_body.strip()) > 50:
                        print("       ✅ Email generation successful")
                        print(f"       📝 Generated length: {len(test_body)} chars")
                        print(f"       📋 Generated preview: {test_body[:100]}...")
                    else:
                        print("       ❌ Email generation failed or too short")
                        print(f"       🔍 Generated: {test_body}")
                        
                except Exception as e:
                    print(f"       ❌ Email generation error: {e}")
            else:
                print("       ⚠️ LLM processor not available for testing")
    else:
        print("✅ All jobs with emails already have email bodies!")
    
    # 4. Analyze the get_email_jobs_needing_generation method
    print("\n4️⃣ Testing database method: get_email_jobs_needing_generation()...")
    
    try:
        method_results = db.get_email_jobs_needing_generation()
        print(f"📊 Method returned {len(method_results)} jobs needing email generation")
        
        if method_results:
            print("✅ Database method is working correctly")
        else:
            print("⚠️ Database method returned 0 results")
            print("   This could mean:")
            print("   - All email jobs already have bodies")
            print("   - Database query condition is too restrictive")
            print("   - Database connection issues")
            
    except Exception as e:
        print(f"❌ Database method failed: {e}")
    
    # 5. Summary and recommendations
    print("\n" + "="*50)
    print("📊 SUMMARY & RECOMMENDATIONS")
    print("="*50)
    
    print(f"\n🎯 Jobs needing email generation: {len(should_have_email_body)}")
    
    if should_have_email_body:
        print("\n⚠️ ISSUES IDENTIFIED:")
        print("1. Jobs with emails are missing email bodies")
        print("2. The email generation process may not be working")
        print("3. Check if user_profile.json exists and is valid")
        print("4. Verify LLM processor can generate emails")
        print("5. Check if the /generate_emails command is being called")
        
        print(f"\n🔧 RECOMMENDED ACTIONS:")
        print("1. Run the generate emails command manually")
        print("2. Check logs for email generation errors")
        print("3. Ensure user_profile.json has required fields")
        print("4. Test individual email generation")
    else:
        print("\n✅ No issues found - all email jobs have bodies!")
        
    print("\n💡 NEXT STEPS:")
    print("1. If jobs need email generation, run /generate_emails command")
    print("2. Check if the Gmail-style email template needs updating")
    print("3. Test the enhanced email generation functionality")

if __name__ == "__main__":
    try:
        analyze_email_generation_issues()
    except KeyboardInterrupt:
        print("\n⚠️ Diagnostic interrupted by user")
    except Exception as e:
        print(f"\n❌ Diagnostic failed with error: {e}")
        import traceback
        traceback.print_exc()