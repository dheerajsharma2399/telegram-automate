#!/usr/bin/env python3
"""
Read latest lines from monitor.log
"""

def read_latest_logs(filename, num_lines=50):
    """Read the last N lines from a file"""
    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            return lines[-num_lines:] if len(lines) > num_lines else lines
    except Exception as e:
        return [f"Error reading {filename}: {e}"]

def main():
    log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', 'app.log')
    print(f"📋 LATEST LOGS ({log_path})")
    print("=" * 60)

    logs = read_latest_logs(log_path, 50)
    
    if logs:
        for i, line in enumerate(logs, 1):
            print(f"{i:3d}: {line.rstrip()}")
    else:
        print("No log entries found or file not accessible")
    
    print("=" * 60)
    print("🏁 END OF LOGS")

if __name__ == "__main__":
    main()