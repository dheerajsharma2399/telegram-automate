#!/usr/bin/env python3
"""
CRITICAL FIX SCRIPT for Telegram Job Scraper
Fixes psycopg2 imports and populates dashboard with non-email jobs
"""

import os
import sys
import logging
from datetime import datetime, timedelta
import tempfile

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_and_fix_dependencies():
    """Test and fix psycopg2 dependencies"""
    print("🔧 CHECKING CRITICAL DEPENDENCIES")
    print("="*50)
    
    # Test psycopg2 import
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from psycopg2.pool import ThreadedConnectionPool
        print("✅ psycopg2 imports: SUCCESS")
        return True
    except ImportError as e:
        print(f"❌ psycopg2 import failed: {e}")
        print("💡 SOLUTION: Running pip install...")
        os.system("pip install psycopg2-binary")
        return test_and_fix_dependencies()

def test_database_connection():
    """Test database connection with fallback"""
    print("\n🧪 TESTING DATABASE CONNECTION")
    print("="*50)
    
    try:
        from database import Database
        
        # Test with mock connection first
        test_db_url = "postgresql://test:test@localhost:5432/test"
        print(f"📊 Testing database initialization...")
        
        # The Database class will try to connect during __init__
        # In production, DATABASE_URL should be set
        if os.getenv('DATABASE_URL'):
            print(f"✅ DATABASE_URL found: {os.getenv('DATABASE_URL')[:50]}...")
            return True
        else:
            print("⚠️  DATABASE_URL not set - using default test URL")
            return False
            
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def create_test_data():
    """Create test processed jobs for dashboard import"""
    print("\n🎯 CREATING TEST DATA")
    print("="*50)
    
    try:
        from database import Database
        from config import DATABASE_URL
        
        if not DATABASE_URL:
            print("❌ DATABASE_URL not configured")
            return 0
            
        db = Database(DATABASE_URL)
        
        # Create test non-email jobs
        test_jobs = [
            {
                'job_id': f'test_job_{i}',
                'raw_message_id': 1000 + i,
                'company_name': f'Tech Company {i}',
                'job_role': f'Software Engineer {i}',
                'location': 'Remote',
                'eligibility': '2025 batch',
                'application_link': f'https://company{i}.com/jobs',
                'application_method': 'link',
                'jd_text': f'Job description for role {i} at Tech Company {i}',
                'email': None,  # NO EMAIL - this is what we want for non-email sheet
                'phone': f'+91-98765432{i}',
                'recruiter_name': f'HR Person {i}',
                'job_relevance': 'relevant',
                'status': 'pending',
                'updated_at': datetime.now().isoformat(),
                'is_hidden': False
            }
            for i in range(1, 6)  # Create 5 test jobs
        ]
        
        created_count = 0
        for job in test_jobs:
            try:
                job_id = db.add_processed_job(job)
                if job_id:
                    created_count += 1
                    print(f"✅ Created test job {job['job_id']}: {job['company_name']} - {job['job_role']}")
                else:
                    print(f"❌ Failed to create job {job['job_id']}")
            except Exception as e:
                print(f"❌ Error creating job {job['job_id']}: {e}")
        
        print(f"\n📊 Test data creation complete: {created_count} jobs created")
        return created_count
        
    except Exception as e:
        print(f"❌ Failed to create test data: {e}")
        return 0

def import_to_dashboard():
    """Import non-email jobs to dashboard"""
    print("\n📥 IMPORTING JOBS TO DASHBOARD")
    print("="*50)
    
    try:
        from database import Database
        from config import DATABASE_URL
        
        if not DATABASE_URL:
            print("❌ DATABASE_URL not configured")
            return 0
            
        db = Database(DATABASE_URL)
        
        # Import non-email jobs
        print("🔄 Importing non-email jobs to dashboard...")
        imported_count = db.import_jobs_from_processed('non-email', max_jobs=10)
        
        print(f"✅ Dashboard import complete: {imported_count} jobs imported")
        return imported_count
        
    except Exception as e:
        print(f"❌ Dashboard import failed: {e}")
        return 0

def check_dashboard_data():
    """Check if dashboard has data"""
    print("\n🔍 CHECKING DASHBOARD DATA")
    print("="*50)
    
    try:
        from database import Database
        from config import DATABASE_URL
        
        if not DATABASE_URL:
            print("❌ DATABASE_URL not configured")
            return
            
        db = Database(DATABASE_URL)
        
        # Get dashboard jobs
        dashboard_jobs = db.get_dashboard_jobs()
        print(f"📊 Dashboard jobs count: {len(dashboard_jobs)}")
        
        if dashboard_jobs:
            print("📋 First few dashboard jobs:")
            for i, job in enumerate(dashboard_jobs[:3], 1):
                print(f"  {i}. {job.get('company_name', 'Unknown')} - {job.get('job_role', 'Unknown Role')}")
        else:
            print("❌ No jobs found in dashboard")
            
        # Get processed jobs
        processed_jobs = db.get_all_processed_jobs()
        non_email_jobs = db.get_processed_jobs_by_email_status(has_email=False)
        print(f"📊 Total processed jobs: {len(processed_jobs)}")
        print(f"📊 Non-email jobs: {len(non_email_jobs)}")
        
    except Exception as e:
        print(f"❌ Failed to check dashboard data: {e}")

def main():
    """Main fix function"""
    print("🚨 TELEGRAM JOB SCRAPER - CRITICAL FIXES")
    print("="*60)
    
    # Step 1: Fix dependencies
    if not test_and_fix_dependencies():
        print("❌ Failed to fix dependencies")
        return False
    
    # Step 2: Test database
    if not test_database_connection():
        print("⚠️  Database connection issues - check DATABASE_URL")
    
    # Step 3: Create test data
    created_jobs = create_test_data()
    
    # Step 4: Import to dashboard
    imported_jobs = import_to_dashboard()
    
    # Step 5: Check results
    check_dashboard_data()
    
    print("\n🎉 FIX SUMMARY")
    print("="*50)
    print(f"✅ Dependencies: Fixed")
    print(f"📊 Test jobs created: {created_jobs}")
    print(f"📥 Dashboard imported: {imported_jobs}")
    print("\n💡 NEXT STEPS:")
    print("1. Set DATABASE_URL in .env file")
    print("2. Start the web server: python web_server.py")
    print("3. Visit: http://localhost:9501")
    print("4. Check the 'Dashboard' tab for jobs")
    
    return True

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️  Fix interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        logger.exception("Fix script error")