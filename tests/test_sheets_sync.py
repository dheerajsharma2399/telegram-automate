#!/usr/bin/env python3
"""
Diagnostic script to check Google Sheets sync status
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from sheets_sync import GoogleSheetsSync
from config import DATABASE_URL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

def main():
    print("=" * 60)
    print("Google Sheets Sync Diagnostic")
    print("=" * 60)
    
    # 1. Check database connection
    print("\n1. Checking database connection...")
    try:
        db = Database(DATABASE_URL)
        print("   ✓ Database connected successfully")
    except Exception as e:
        print(f"   ✗ Database connection failed: {e}")
        return
    
    # 2. Check unsynced jobs
    print("\n2. Checking unsynced jobs...")
    try:
        unsynced = db.jobs.get_unsynced_jobs()
        print(f"   Total unsynced jobs: {len(unsynced)}")
        if unsynced:
            print(f"   Sample job IDs:")
            for job in unsynced[:5]:
                print(f"     - {job.get('job_id')} | {job.get('company_name')} | {job.get('job_role')}")
    except Exception as e:
        print(f"   ✗ Failed to get unsynced jobs: {e}")
    
    # 3. Check Google Sheets configuration
    print("\n3. Checking Google Sheets configuration...")
    try:
        if not GOOGLE_CREDENTIALS_JSON:
            print("   ✗ GOOGLE_CREDENTIALS_JSON not set")
            return
        if not SPREADSHEET_ID:
            print("   ✗ SPREADSHEET_ID not set")
            return
        print("   ✓ Credentials and Spreadsheet ID are configured")
    except Exception as e:
        print(f"   ✗ Configuration check failed: {e}")
        return
    
    # 4. Test Google Sheets connection
    print("\n4. Testing Google Sheets connection...")
    try:
        sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        if sync.client:
            print("   ✓ Google Sheets client initialized")
            print(f"   ✓ Email sheet: {'Available' if sync.sheet_email else 'Not available'}")
            print(f"   ✓ Non-email sheet: {'Available' if sync.sheet_other else 'Not available'}")
            print(f"   ✓ Email-exp sheet: {'Available' if sync.sheet_email_exp else 'Not available'}")
            print(f"   ✓ Non-email-exp sheet: {'Available' if sync.sheet_other_exp else 'Not available'}")
        else:
            print("   ✗ Google Sheets client failed to initialize")
            return
    except Exception as e:
        print(f"   ✗ Google Sheets connection failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 5. Test sync with one job
    print("\n5. Testing sync with one job...")
    if unsynced:
        test_job = unsynced[0]
        print(f"   Testing with job: {test_job.get('job_id')}")
        try:
            result = sync.sync_job(test_job)
            if result:
                print("   ✓ Test sync successful!")
                # Mark as synced
                db.jobs.mark_job_synced(test_job.get('job_id'))
                print("   ✓ Job marked as synced in database")
            else:
                print("   ✗ Test sync failed")
        except Exception as e:
            print(f"   ✗ Sync error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("   No unsynced jobs to test with")
    
    print("\n" + "=" * 60)
    print("Diagnostic complete")
    print("=" * 60)

if __name__ == "__main__":
    main()
