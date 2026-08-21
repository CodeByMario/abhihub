#!/usr/bin/env python3
"""Apply migration 017: add program column to documents table."""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL or SUPABASE_KEY not set")
    sys.exit(1)

# Read migration SQL
migration_path = os.path.join(os.path.dirname(__file__), "migrations", "017_add_program_column.sql")
with open(migration_path) as f:
    sql = f.read()

# Split into statements
statements = [s.strip() for s in sql.split(";") if s.strip()]

# Use Supabase client to run each statement
try:
    from supabase import create_client, ClientOptions
    client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="abhihub"))
except ImportError:
    print("ERROR: supabase-py not installed")
    sys.exit(1)

for stmt in statements:
    if not stmt:
        continue
    # Supabase Python client doesn't have a direct "run raw SQL" method,
    # so we use the RPC approach with postgres functions or
    # we use the .rpc() method
    try:
        # Try using rpc with a special endpoint if available
        # Fallback: use the REST API directly
        import requests
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        payload = {"query": stmt}
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/rpc/execute_sql", json=payload, headers=headers)
        if resp.status_code == 200:
            print(f"OK: {stmt[:80]}...")
        else:
            print(f"WARN ({resp.status_code}): {stmt[:80]}...")
            if resp.text:
                print(f"  Response: {resp.text[:200]}")
    except Exception as e:
        print(f"ERROR executing '{stmt[:80]}...': {e}")

print("\nMigration 017 applied.")
