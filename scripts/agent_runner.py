#!/usr/bin/env python3
import os
import sys
import asyncio
import aiohttp
import argparse
from datetime import datetime

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import OPENROUTER_API_KEY, OPENROUTER_MODEL
except ImportError:
    print("Error: Could not import config.py. Make sure you are in the project root.")
    sys.exit(1)

RALPH_DIR = ".ralph-loops"
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

def get_file_content(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

async def run_agent_loop(loop_name, auto_log=False, prompt_file=None):
    loop_path = os.path.join(RALPH_DIR, loop_name)
    if not os.path.exists(loop_path):
        print(f"Error: Loop '{loop_name}' not found.")
        return

    print(f"🔄 Running Agent Loop: {loop_name}...")

    # Read Context
    if prompt_file:
        if os.path.exists(prompt_file):
             print(f"📄 Loading Custom Prompt: {prompt_file}")
             prompt_sys = get_file_content(prompt_file)
        else:
             print(f"❌ Error: Custom prompt file '{prompt_file}' not found.")
             return
    else:
        prompt_sys = get_file_content(os.path.join(loop_path, "prompt.md"))

    prd_content = get_file_content(os.path.join(loop_path, "PRD.md"))
    progress_content = get_file_content(os.path.join(loop_path, "progress.txt"))

    # ... (rest of the function) ...

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GSD Agent Runner")
    parser.add_argument("loop", help="Name of the loop to run (e.g., kilo, claude)")
    parser.add_argument("--prompt-file", help="Path to a custom prompt file to use", default=None)
    parser.add_argument("--auto-log", action="store_true", help="Automatically append [LOG] lines to progress.txt")
    
    args = parser.parse_args()
    asyncio.run(run_agent_loop(args.loop, args.auto_log, args.prompt_file))
