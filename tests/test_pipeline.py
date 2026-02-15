import asyncio
import os
import csv
import sys
from dotenv import load_dotenv
from llm_processor import LLMProcessor
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL

# Load environment variables
load_dotenv()

async def run_test():
    print("--- Telegram Job Scraper Pipeline Test ---")
    
    if not OPENROUTER_API_KEY:
        print("Error: OPENROUTER_API_KEY not found in environment variables.")
        return

    # Initialize Processor
    processor = LLMProcessor(OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL)
    print(f"Initialized LLMProcessor with model: {OPENROUTER_MODEL}")

    # Get Input
    print("\nPaste your raw Telegram message below (Press Ctrl+Z then Enter on Windows to finish, or Ctrl+D on Linux/Mac):")
    try:
        # Read multiline input
        lines = sys.stdin.readlines()
        raw_message = "".join(lines)
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return

    if not raw_message.strip():
        print("No message provided. Exiting.")
        return

    print("\nProcessing message... (this calls the LLM and applies all fixes)")
    
    try:
        # Run the pipeline
        jobs = await processor.parse_jobs(raw_message)
        
        if not jobs:
            print("No jobs found!")
            return

        print(f"\nSuccessfully extracted {len(jobs)} jobs.")
        
        # Save to CSV
        csv_filename = "test_processed_data.csv"
        if jobs:
            keys = jobs[0].keys()
            with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(jobs)
            print(f"\nData saved to: {os.path.abspath(csv_filename)}")

        # Print detailed preview
        print("\n--- Processed Data Preview ---")
        for i, job in enumerate(jobs):
            print(f"\n[Job {i+1}]")
            print(f"Company: {job.get('company_name')}")
            print(f"Role: {job.get('job_role')}")
            print(f"Email: {job.get('email')}")
            print(f"Link: {job.get('application_link')}")
            print(f"JD Text Length: {len(job.get('jd_text', ''))} chars")
            print(f"JD Snippet: {job.get('jd_text', '')[:100]}...")

    except Exception as e:
        print(f"\nError during processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Windows-specific asyncio policy fix
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(run_test())
