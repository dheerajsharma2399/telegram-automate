#!/usr/bin/env python3
import os
import sys
import argparse
import datetime

RALPH_DIR = ".ralph-loops"

def get_loop_path(loop_name):
    return os.path.join(RALPH_DIR, loop_name)

def ensure_loop_exists(loop_name):
    path = get_loop_path(loop_name)
    if not os.path.exists(path):
        print(f"Error: Loop '{loop_name}' does not exist.")
        sys.exit(1)
    return path

def setup_loop(args):
    path = get_loop_path(args.name)
    if os.path.exists(path):
        print(f"Loop '{args.name}' already exists.")
        return

    os.makedirs(path)
    
    # Create files
    with open(os.path.join(path, "prompt.md"), "w") as f:
        f.write(f"# Agent Role: {args.name}\n\nDefine your role here.")
    
    with open(os.path.join(path, "PRD.md"), "w") as f:
        f.write(f"# {args.name} Tasks\n\n- [ ] Initial Task")
        
    with open(os.path.join(path, "progress.txt"), "w") as f:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        f.write(f"[{timestamp}] Loop initialized.\n")
        
    print(f"Created loop '{args.name}' in {path}")

def add_task(args):
    loop_path = ensure_loop_exists(args.loop)
    prd_path = os.path.join(loop_path, "PRD.md")
    
    with open(prd_path, "a") as f:
        f.write(f"\n- [ ] {args.description}")
    
    print(f"Added task to {args.loop}: {args.description}")

def log_progress(args):
    loop_path = ensure_loop_exists(args.loop)
    prog_path = os.path.join(loop_path, "progress.txt")
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"[{timestamp}] {args.message}\n"
    
    with open(prog_path, "a") as f:
        f.write(entry)
        
    print(f"Logged to {args.loop}: {entry.strip()}")

def show_status(args):
    loop_path = ensure_loop_exists(args.loop)
    
    print(f"\n--- Status: {args.loop} ---")
    
    # Last 3 log entries
    print("\n[Recent Progress]")
    with open(os.path.join(loop_path, "progress.txt"), "r") as f:
        lines = f.readlines()
        for line in lines[-3:]:
            print(line.strip())
            
    # Next task
    print("\n[Next Task]")
    with open(os.path.join(loop_path, "PRD.md"), "r") as f:
        for line in f:
            if "- [ ]" in line:
                print(line.strip())
                break
    print("-------------------")

def main():
    parser = argparse.ArgumentParser(description="GSD / Ralph Loop Manager")
    subparsers = parser.add_subparsers()

    # Init
    p_init = subparsers.add_parser("init", help="Create a new loop")
    p_init.add_argument("name", help="Name of the loop (e.g., kilo, claude)")
    p_init.set_defaults(func=setup_loop)

    # Task
    p_task = subparsers.add_parser("task", help="Add a task to a loop")
    p_task.add_argument("loop", help="Loop name")
    p_task.add_argument("description", help="Task description")
    p_task.set_defaults(func=add_task)
    
    # Log
    p_log = subparsers.add_parser("log", help="Log progress")
    p_log.add_argument("loop", help="Loop name")
    p_log.add_argument("message", help="Progress message")
    p_log.set_defaults(func=log_progress)

    # Status
    p_status = subparsers.add_parser("status", help="Show loop status")
    p_status.add_argument("loop", help="Loop name")
    p_status.set_defaults(func=show_status)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
