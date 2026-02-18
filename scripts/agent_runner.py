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

async def run_agent_loop(loop_name, auto_log=False):
    loop_path = os.path.join(RALPH_DIR, loop_name)
    if not os.path.exists(loop_path):
        print(f"Error: Loop '{loop_name}' not found.")
        return

    print(f"🔄 Running Agent Loop: {loop_name}...")

    # Read Context
    prompt_sys = get_file_content(os.path.join(loop_path, "prompt.md"))
    prd_content = get_file_content(os.path.join(loop_path, "PRD.md"))
    progress_content = get_file_content(os.path.join(loop_path, "progress.txt"))

    # Construct Prompt
    user_message = f"""
# CURRENT STATE
Here is the Project Requirements Document (PRD):
{prd_content}

Here is the Progress Log so far:
{progress_content}

# INSTRUCTION
Based on the PRD and Progress Log:
1. Identify the next incomplete task.
2. Perform the necessary analysis or code generation.
3. Provide your output clearly.
4. End your response with a log entry formatted as: `[LOG] <message>` which I can append to the progress file.
"""

    messages = [
        {"role": "system", "content": prompt_content if 'prompt_content' in locals() else prompt_sys},
        {"role": "user", "content": user_message}
    ]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "GSD Agent Runner"
    }

    payload = {
        "model": OPENROUTER_MODEL or "anthropic/claude-3.5-sonnet",
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 4000
    }

    print("🤖 Thinking... (Calling OpenRouter)")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(BASE_URL, headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data['choices'][0]['message']['content']
                    
                    print("\n" + "="*40)
                    print(f"📢 AGENT RESPONSE ({loop_name})")
                    print("="*40)
                    print(content)
                    print("="*40 + "\n")

                    # Auto-Log extraction
                    if auto_log:
                        import re
                        log_match = re.search(r'\[LOG\]\s*(.*)', content)
                        if log_match:
                            log_msg = log_match.group(1).strip()
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                            entry = f"[{timestamp}] {log_msg}\n"
                            
                            with open(os.path.join(loop_path, "progress.txt"), "a") as f:
                                f.write(entry)
                            print(f"✅ Auto-logged: {log_msg}")
                        else:
                            print("⚠️ No [LOG] tag found in response. Progress not updated.")

                else:
                    err = await response.text()
                    print(f"❌ Error: HTTP {response.status} - {err}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GSD Agent Runner")
    parser.add_argument("loop", help="Name of the loop to run (e.g., kilo, claude)")
    parser.add_argument("--auto-log", action="store_true", help="Automatically append [LOG] lines to progress.txt")
    
    args = parser.parse_args()
    asyncio.run(run_agent_loop(args.loop, args.auto_log))
