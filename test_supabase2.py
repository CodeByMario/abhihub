import os
from dotenv import load_dotenv
from supabase import create_client, ClientOptions

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY_AON") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
client = create_client(url, key, options=ClientOptions(schema="abhihub"))

try:
    res = client.table("documents").select("id").limit(1).execute()
    print("SUCCESS reading documents table")
except Exception as e:
    print("ERROR reading documents:", e)
