
import os
import sys
import asyncio
import logging

# Add root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from config import DATABASE_URL, OPENROUTER_API_KEYS, OPENROUTER_MODELS, OPENROUTER_FALLBACK_MODELS
from llm_processor import LLMProcessor

# Setup logging
logging.basicConfig(level=logging.INFO)

async def debug_message(message_id):
    print(f"--- Debugging Message {message_id} ---")
    
    db = Database(DATABASE_URL)
    
    # 1. Get Message Text
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT message_text FROM raw_messages WHERE id = %s", (message_id,))
            result = cursor.fetchone()
            if not result:
                print("Message not found!")
                return
            message_text = result['message_text']
            
    print(f"Message Text (first 100 chars): {message_text[:100]}...")
    
    # 2a. Test Regex Fallback
    print("\n--- Testing Regex Fallback ---")
    processor = LLMProcessor(OPENROUTER_API_KEYS, OPENROUTER_MODELS, OPENROUTER_FALLBACK_MODELS)
    regex_jobs = processor._regex_fallback(message_text)
    print(f"Regex found {len(regex_jobs)} jobs.")
    for j in regex_jobs:
        print(f"  Regex Job: {j.get('company_name')} - {j.get('job_role')}")

    # 2. Run LLM
    print("\nRunning LLM...")
    jobs = await processor.parse_jobs(message_text)
    
    print(f"\nLLM Found {len(jobs) if jobs else 0} jobs.")
    
    if not jobs:
        print("No jobs found by LLM.")
        return

    # 3. Check Duplicates
    for i, job in enumerate(jobs):
        print(f"\nJob #{i+1}:")
        print(f"  Company: {job.get('company_name')}")
        print(f"  Role: {job.get('job_role')}")
        
        dup = db.jobs.find_duplicate_processed_job(
            job.get('company_name'),
            job.get('job_role'),
            job.get('email')
        )
        
        if dup:
            print(f"  [DUPLICATE DETECTED]")
            print(f"  Original Job ID: {dup.get('job_id')}")
            print(f"  Original Created At: {dup.get('created_at')}")
        else:
            print("  [NEW JOB]")
            print("  Attempting insertion...")
            try:
                # Process data
                processed_data = processor.process_job_data(job, message_id)
                print(f"  Processed Data keys: {list(processed_data.keys())}")
                
                # Insert
                new_id = db.jobs.add_processed_job(processed_data)
                
                if new_id:
                    print(f"  ✅ SUCCESS! Inserted Job ID: {new_id}")
                else:
                    print(f"  ❌ FAILED! add_processed_job returned None")
            except Exception as e:
                print(f"  ❌ EXCEPTION during insertion: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        msg_id = int(sys.argv[1])
    else:
        msg_id = 556 # Default to the one we saw in logs
        
    asyncio.run(debug_message(msg_id))
