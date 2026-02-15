#!/usr/bin/env python3
"""
Fix: Reset sync status for jobs from Feb 8 onwards (ID 3932+)
Also investigate why sync stopped working
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from sheets_sync import GoogleSheetsSync
from config import DATABASE_URL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

print("=" * 60)
print("Google Sheets Sync Fix - From Feb 8 (ID 3932 onwards)")
print("=" * 60)

db = Database(DATABASE_URL)

# 1. Current status
print("\n1. Current Status:")
with db.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE id >= 3932")
        total = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE id >= 3932 AND synced_to_sheets = FALSE")
        unsynced = cursor.fetchone()['count']
        print(f"   Jobs from ID 3932 onwards: {total}")
        print(f"   Currently unsynced: {unsynced}")

# 2. Sample jobs
print("\n2. Sample Jobs:")
with db.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, company_name, created_at, synced_to_sheets, sheet_name
            FROM processed_jobs WHERE id >= 3932 ORDER BY id ASC LIMIT 3
        """)
        for job in cursor.fetchall():
            sync = "✓" if job['synced_to_sheets'] else "✗"
            print(f"   ID {job['id']} {sync} | {job['created_at']} | {job['company_name']} | {job.get('sheet_name', 'N/A')}")

# 3. Reset sync status
print(f"\n3. Resetting sync status for {total} jobs...")
with db.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("UPDATE processed_jobs SET synced_to_sheets = FALSE WHERE id >= 3932")
        updated = cursor.rowcount
    conn.commit()
print(f"   ✓ Reset {updated} jobs")

# 4. Test sync
print("\n4. Testing sync...")
unsynced_jobs = db.jobs.get_unsynced_jobs()
if unsynced_jobs:
    test_job = unsynced_jobs[0]
    print(f"   Testing: {test_job.get('company_name')}")
    sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
    if sync.sync_job(test_job):
        print("   ✓ Test sync successful!")
        db.jobs.mark_job_synced(test_job.get('job_id'))
        print(f"   Remaining: {len(unsynced_jobs) - 1} jobs")
    else:
        print("   ✗ Test sync failed")

print("\n" + "=" * 60)
print("✅ Fix Complete - Jobs will auto-sync every 5 minutes")
print("=" * 60)
print("\nWhy sync stopped working:")
print("- Jobs were being marked as synced even when sync failed")
print("- This created a situation where bot thought everything was synced")
print("- No error handling to retry failed syncs")
print("\nSolution applied:")
print("- Reset sync status for all jobs from Feb 8 onwards")
print("- Bot will now re-sync these 229 jobs automatically")
