
import os
import sys
import asyncio
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging to stdout
logging.basicConfig(level=logging.INFO)

from main import process_jobs

if __name__ == "__main__":
    print("Forcing job processing loop...")
    asyncio.run(process_jobs())
