#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import Database
from config import DATABASE_URL

db = Database(DATABASE_URL)
with db.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT MAX(id) as max_id FROM processed_jobs")
        print(f"Max ID: {cursor.fetchone()['max_id']}")
        
        cursor.execute("SELECT id, created_at FROM processed_jobs WHERE created_at::date = '2026-02-08' ORDER BY id LIMIT 1")
        feb8 = cursor.fetchone()
        if feb8:
            print(f"First job on Feb 8: ID {feb8['id']}, Date: {feb8['created_at']}")
        else:
            print("No jobs on Feb 8")
        
        cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE created_at >= '2026-02-08'")
        print(f"Jobs from Feb 8 onwards: {cursor.fetchone()['count']}")
