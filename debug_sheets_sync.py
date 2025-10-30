#!/usr/bin/env python3
"""
Google Sheets Sync Diagnostic Tool

This script helps debug why Google Sheets sync reports success but sheets remain empty.
Run this script to identify issues with:
1. Database job data structure
2. Google Sheets connection
3. Data mapping problems
"""

import os
import sys
import json
from datetime import datetime

# Add current directory to path for imports
sys.path.append('.')

from database import Database
from sheets_sync import GoogleSheetsSync
from config import (
    GOOGLE_CREDENTIALS_JSON, 
    SPREADSHEET_ID,
    OPENROUTER_API_KEY, 
    OPENROUTER_MODEL, 
    OPENROUTER_FALLBACK_MODEL
)
from llm_processor import LLMProcessor

def main():
    print("🔍 Google Sheets Sync Diagnostic Tool")
    print("=" * 50)
    
    # 1. Check environment
    print("\n1. 📋 Environment Check")
    print("-" * 30)
    
    if not GOOGLE_CREDENTIALS_JSON:
        print("❌ GOOGLE_CREDENTIALS_JSON not configured")
        return
    else:
        print("✅ GOOGLE_CREDENTIALS_JSON is set")
    
    if not SPREADSHEET_ID:
        print("❌ SPREADSHEET_ID not configured")
        return
    else:
        print(f"✅ SPREADSHEET_ID: {SPREADSHEET_ID}")
    
    # 2. Initialize database
    print("\n2. 💾 Database Connection")
    print("-" * 30)
    
    try:
        db = Database("jobs.db")
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    # 3. Check for unsynced jobs
    print("\n3. 📊 Unsynced Jobs Check")
    print("-" * 30)
    
    try:
        unsynced_jobs = db.get_unsynced_jobs()
        print(f"✅ Found {len(unsynced_jobs)} unsynced jobs")
        
        if unsynced_jobs:
            print("\n📋 Sample job data structure:")
            sample_job = unsynced_jobs[0]
            print(f"Available fields: {list(sample_job.keys())}")
            
            print("\n🔍 Field mapping analysis:")
            expected_fields = [
                'job_id', 'company_name', 'job_role', 'location', 'eligibility',
                'email', 'phone', 'recruiter_name', 'application_link', 
                'application_method', 'jd_text', 'email_subject', 'email_body',
                'status', 'created_at', 'job_relevance', 'experience_required'
            ]
            
            for field in expected_fields:
                if field in sample_job:
                    value = sample_job[field]
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:50] + "..."
                    print(f"  ✅ {field}: {value}")
                else:
                    print(f"  ❌ {field}: MISSING")
        else:
            print("⚠️  No unsynced jobs found. Database might be empty or all jobs synced.")
            
    except Exception as e:
        print(f"❌ Error fetching unsynced jobs: {e}")
        return
    
    # 4. Initialize Google Sheets
    print("\n4. 📈 Google Sheets Connection")
    print("-" * 30)
    
    try:
        sheets_sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        
        if not sheets_sync.client:
            print("❌ Google Sheets client initialization failed")
            print("Possible causes:")
            print("  - Invalid credentials JSON")
            print("  - Wrong spreadsheet ID")
            print("  - Network connectivity issues")
            return
        else:
            print("✅ Google Sheets client initialized successfully")
            
    except Exception as e:
        print(f"❌ Google Sheets initialization error: {e}")
        return
    
    # 5. Check worksheets
    print("\n5. 📊 Worksheets Check")
    print("-" * 30)
    
    try:
        worksheets_info = {}
        expected_sheets = ['email', 'non-email', 'email-exp', 'non-email-exp']
        
        for sheet_name in expected_sheets:
            worksheet = None
            try:
                if sheet_name == 'email':
                    worksheet = sheets_sync.sheet_email
                elif sheet_name == 'non-email':
                    worksheet = sheets_sync.sheet_other
                elif sheet_name == 'email-exp':
                    worksheet = sheets_sync.sheet_email_exp
                elif sheet_name == 'non-email-exp':
                    worksheet = sheets_sync.sheet_other_exp
                
                if worksheet:
                    # Check worksheet details
                    values = worksheet.get_all_values()
                    if values:
                        print(f"✅ {sheet_name}: {len(values)-1} data rows (plus header)")
                        worksheets_info[sheet_name] = {
                            'total_rows': len(values),
                            'data_rows': len(values) - 1,
                            'headers': values[0] if values else []
                        }
                    else:
                        print(f"⚠️  {sheet_name}: Empty (only header)")
                        worksheets_info[sheet_name] = {
                            'total_rows': 0,
                            'data_rows': 0,
                            'headers': []
                        }
                else:
                    print(f"❌ {sheet_name}: Worksheet not found")
                    
            except Exception as e:
                print(f"❌ {sheet_name}: Error accessing worksheet - {e}")
        
    except Exception as e:
        print(f"❌ Error checking worksheets: {e}")
        return
    
    # 6. Test sync with first job
    print("\n6. 🔧 Test Sync")
    print("-" * 30)
    
    if unsynced_jobs:
        sample_job = unsynced_jobs[0]
        print(f"Testing sync with job_id: {sample_job.get('job_id', 'unknown')}")
        
        try:
            result = sheets_sync.sync_job(sample_job)
            if result:
                print("✅ Sync test PASSED - data was written to sheet")
            else:
                print("❌ Sync test FAILED - no data written")
                
        except Exception as e:
            print(f"❌ Sync test ERROR: {e}")
    
    # 7. Summary and recommendations
    print("\n7. 📝 Analysis Summary")
    print("=" * 50)
    
    print("\n🎯 Potential Issues:")
    print("1. Data mapping mismatch between database and sheets")
    print("2. Missing required fields (job_relevance, experience_required)")
    print("3. Google Sheets API permissions")
    print("4. Worksheet column mismatch")
    
    print("\n🔧 Next Steps:")
    print("1. Run this diagnostic regularly")
    print("2. Check Google Sheets API quotas and permissions")
    print("3. Verify spreadsheet sharing with service account")
    print("4. Consider adding detailed logging to sync operations")

if __name__ == "__main__":
    main()