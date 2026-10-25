import os
import sys
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.getenv('SUPABASE_URL')
anon_key = os.getenv('SUPABASE_PUBLIC_API_KEY') or os.getenv('SUPABASE_KEY')

if not supabase_url or not anon_key:
    print("[ERROR] SUPABASE_URL or SUPABASE_PUBLIC_API_KEY missing from .env")
    sys.exit(1)

from supabase import create_client, ClientOptions

print(f"Connecting to {supabase_url} with anon key (schema: abhihub)...")
client = create_client(supabase_url, anon_key, options=ClientOptions(schema="abhihub"))

tables_to_test = [
    ("search_analytics", "insert", {
        "query": "__test_rls_probe__",
        "results_count": 0
    }),
    ("search_analytics", "select", None),
    ("notifications", "select", None),
    ("profiles", "select", None),
]

for table, action, payload in tables_to_test:
    try:
        if action == "insert":
            res = client.table(table).insert(payload).execute()
            print(f"[PASS] {table} INSERT allowed under RLS")
            # Cleanup probe row if possible
            try:
                client.table(table).delete().eq("query", "__test_rls_probe__").execute()
            except Exception:
                pass
        elif action == "select":
            res = client.table(table).select("*").limit(1).execute()
            print(f"[PASS] {table} SELECT allowed under RLS (returned {len(res.data or [])} rows)")
    except Exception as e:
        print(f"[FAIL] {table} {action.upper()} blocked by RLS: {e}")
