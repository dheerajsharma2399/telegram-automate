#!/usr/bin/env python3
"""
Quick verification that dashboard is working
"""

import os
import sys

def verify_dashboard():
    """Verify dashboard has data"""
    print("🔍 DASHBOARD VERIFICATION")
    print("="*40)
    
    try:
        from database import Database
        from config import DATABASE_URL
        
        if not DATABASE_URL:
            print("❌ DATABASE_URL not configured")
            return False
            
        db = Database(DATABASE_URL)
        
        # Get dashboard jobs
        dashboard_jobs = db.get_dashboard_jobs()
        print(f"✅ Dashboard jobs: {len(dashboard_jobs)}")
        
        if dashboard_jobs:
            print("📋 Sample jobs:")
            for i, job in enumerate(dashboard_jobs[:3], 1):
                company = job.get('company_name', 'Unknown')
                role = job.get('job_role', 'Unknown Role')
                status = job.get('application_status', 'not_applied')
                print(f"  {i}. {company} - {role} ({status})")
            return True
        else:
            print("❌ No jobs in dashboard")
            return False
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    verify_dashboard()