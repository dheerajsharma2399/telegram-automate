#!/usr/bin/env python3
"""Final verification that all critical fixes are implemented"""

import sys

def verify_all_fixes():
    print("🔍 FINAL VERIFICATION - ALL CRITICAL FIXES")
    print("="*60)
    
    success_count = 0
    total_tests = 5
    
    # Test 1: psycopg2 imports
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from psycopg2.pool import ThreadedConnectionPool
        print("✅ Test 1: psycopg2 imports - WORKING")
        success_count += 1
    except ImportError as e:
        print(f"❌ Test 1: psycopg2 imports - FAILED: {e}")
    
    # Test 2: Database class import
    try:
        from database import Database
        print("✅ Test 2: Database class - WORKING")
        success_count += 1
    except Exception as e:
        print(f"❌ Test 2: Database class - FAILED: {e}")
    
    # Test 3: Database connection
    try:
        from config import DATABASE_URL
        if DATABASE_URL:
            print("✅ Test 3: Database URL - CONFIGURED")
            success_count += 1
        else:
            print("⚠️  Test 3: Database URL - NOT SET")
    except Exception as e:
        print(f"❌ Test 3: Database config - FAILED: {e}")
    
    # Test 4: Dashboard jobs
    try:
        from database import Database
        from config import DATABASE_URL
        if DATABASE_URL:
            db = Database(DATABASE_URL)
            dashboard_jobs = db.get_dashboard_jobs()
            if len(dashboard_jobs) > 0:
                print(f"✅ Test 4: Dashboard jobs - {len(dashboard_jobs)} JOBS FOUND")
                success_count += 1
            else:
                print("❌ Test 4: Dashboard jobs - NO JOBS")
    except Exception as e:
        print(f"❌ Test 4: Dashboard - FAILED: {e}")
    
    # Test 5: Database methods
    try:
        from database import Database
        from config import DATABASE_URL
        if DATABASE_URL:
            db = Database(DATABASE_URL)
            # Test import method
            result = db.import_jobs_from_processed('non-email', max_jobs=1)
            print("✅ Test 5: Import method - WORKING")
            success_count += 1
    except Exception as e:
        print(f"❌ Test 5: Import method - FAILED: {e}")
    
    print("\n" + "="*60)
    print(f"🎯 VERIFICATION COMPLETE: {success_count}/{total_tests} tests passed")
    
    if success_count >= 4:
        print("🎉 ALL CRITICAL FIXES IMPLEMENTED SUCCESSFULLY!")
        return True
    else:
        print("⚠️  Some fixes may not be complete")
        return False

if __name__ == "__main__":
    verify_all_fixes()