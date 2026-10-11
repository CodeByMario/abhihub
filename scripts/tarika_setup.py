"""Tarika AI one-time setup. Safe to re-run: exits early once locked."""
import os
import sys
import pathlib
import httpx
from datetime import datetime, timezone

# Ensure project root is in sys.path
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from supabase import create_client, ClientOptions
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = (
    os.environ.get("SUPABASE_SECRET_API_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_JWT")
    or os.environ.get("SUPABASE_KEY")
)

if not supabase_url or not supabase_key:
    print("❌ ERROR: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing in environment.")
    sys.exit(1)

db = create_client(supabase_url, supabase_key, options=ClientOptions(schema="abhihub"))


def done():
    try:
        r = db.table("ai_config").select("value").eq("key", "setup_completed").execute()
        return bool(r.data and r.data[0]["value"].get("ok"))
    except Exception:
        return False

if done() and "--force" not in sys.argv:
    print("Setup already completed. Use --force to re-run.")
    sys.exit(0)

def log(name, ok, details=""):
    try:
        db.table("ai_setup_checks").insert(
            {"check_name": name, "passed": ok, "details": str(details)[:500]}
        ).execute()
    except Exception as exc:
        print(f"Warning: unable to log check to DB ({exc})")
    print(("PASS " if ok else "FAIL ") + name, details)
    return ok

PROVIDERS = {
  "openrouter": (["OPENROUTER_API_KEY"], "https://openrouter.ai/api/v1/models", "bearer", True),
  "gemini":     (["GEMINI_API_KEY", "GEMINI_API"],
                 "https://generativelanguage.googleapis.com/v1beta/models?key={key}", "query", True),
  "groq":       (["GROQ_API_KEY"], "https://api.groq.com/openai/v1/models", "bearer", False),
  "cerebras":   (["CEREBRAS_API_KEY"], "https://api.cerebras.ai/v1/models", "bearer", False),
  "mistral":    (["MISTRAL_API_KEY"], "https://api.mistral.ai/v1/models", "bearer", False),
}

required_ok = True
for name, (env_vars, url, auth, required) in PROVIDERS.items():
    key = next((os.getenv(e, "").strip().strip("'\"") for e in env_vars if os.getenv(e, "").strip()), "")
    if not key:
        ok = log(f"key:{name}", not required, "missing" + (" (REQUIRED)" if required else " (optional, skipped)"))
        required_ok &= ok
        continue
    try:
        headers = {"Authorization": f"Bearer {key}"} if auth == "bearer" else {}
        r = httpx.get(url.format(key=key), headers=headers, timeout=20)
        ok = log(f"key:{name}", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        ok = log(f"key:{name}", False, str(e))
    required_ok &= (ok or not required)

fernet_key = os.getenv("BYOK_FERNET_KEY") or os.getenv("FERNET_KEY") or os.getenv("FERNET_KEYS")
enc_ok = log("fernet_key", bool(fernet_key and fernet_key.strip()))

tables_ok = True
for t in ["user_ai_keys", "model_catalog", "model_status_events", "ai_usage_log", "ai_config"]:
    try:
        db.table(t).select("*").limit(1).execute()
        log(f"table:{t}", True)
    except Exception as e:
        tables_ok = log(f"table:{t}", False, str(e))

# First sync
sync_ok = False
try:
    from services.catalog_sync import sync_all
    import asyncio
    asyncio.run(sync_all())
    res = db.table("model_catalog").select("id").eq("status", "free_verified").execute()
    n = len(res.data) if res.data else 0
    sync_ok = log("first_sync", n > 0, f"{n} free_verified models")
except Exception as e:
    sync_ok = log("first_sync", False, str(e))

if required_ok and enc_ok and tables_ok and sync_ok:
    db.table("ai_config").upsert({"key": "setup_completed", "value":
        {"ok": True, "at": datetime.now(timezone.utc).isoformat()}}).execute()
    print("\n✅ SETUP COMPLETE and locked. You never need to run this again.")
else:
    print("\n❌ Fix the FAIL lines above, then re-run. Nothing was locked.")
