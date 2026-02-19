#!/usr/bin/env python3
"""
Run database migrations against PostgreSQL
Usage: python scripts/run_migrations.py
"""
import os
import sys
import psycopg2
from pathlib import Path

# Database connection settings from .env
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://***REMOVED***@***REMOVED***:5432/telegram_bot')

def parse_db_url(url):
    """Parse PostgreSQL URL to connection parameters"""
    # Format: postgresql://user:password@host:port/database
    url = url.replace('postgresql://', '').replace('postgres://', '')
    parts = url.split('@')
    credentials = parts[0].split(':')
    host_port_db = parts[1].split('/')
    host_port = host_port_db[0].split(':')
    
    return {
        'host': host_port[0],
        'port': int(host_port[1]) if len(host_port) > 1 else 5432,
        'database': host_port_db[1],
        'user': credentials[0],
        'password': credentials[1]
    }

def run_migration_file(conn, filepath):
    """Execute a single SQL migration file"""
    print(f"Running migration: {filepath}")
    with open(filepath, 'r') as f:
        sql = f.read()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        conn.commit()
        print(f"  ✓ Success")
        return True
    except Exception as e:
        conn.rollback()
        print(f"  ✗ Error: {e}")
        return False
    finally:
        cursor.close()

def main():
    # Get migrations directory
    migrations_dir = Path(__file__).parent / 'migrations'
    
    if not migrations_dir.exists():
        print(f"Error: Migrations directory not found: {migrations_dir}")
        sys.exit(1)
    
    # Get all SQL files sorted
    migration_files = sorted(migrations_dir.glob('*.sql'))
    
    if not migration_files:
        print("No migration files found")
        sys.exit(1)
    
    print(f"Found {len(migration_files)} migration files")
    
    # Connect to database
    db_params = parse_db_url(DATABASE_URL)
    print(f"Connecting to {db_params['host']}:{db_params['port']}/{db_params['database']}...")
    
    try:
        conn = psycopg2.connect(**db_params)
        print("Connected successfully")
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)
    
    # Run each migration
    success_count = 0
    for migration_file in migration_files:
        if run_migration_file(conn, migration_file):
            success_count += 1
    
    conn.close()
    
    print(f"\n{success_count}/{len(migration_files)} migrations completed successfully")
    
    if success_count != len(migration_files):
        sys.exit(1)

if __name__ == '__main__':
    main()
