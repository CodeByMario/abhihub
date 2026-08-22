"""
Configuration for the AbhiHub autonomous company bots.

Every setting is safe to run with NO environment variables:
- Missing OPENROUTER_API_KEY  -> deterministic local reasoning (no LLM)
- Missing SUPABASE_URL/KEY    -> local data estimates (no DB)
"""
import os

# --- Load .env if present (python-dotenv may not be importable everywhere) ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # best-effort: parse .env manually so the bots run without the dep
    try:
        # repo root is two levels up from dev/bots/config.py
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        env_path = os.path.join(_root, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "abhihub.run.place")
API_BASE = os.environ.get("API_BASE", f"https://{BASE_DOMAIN}")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Model used for real LLM reasoning (cheap + capable).
LLM_MODEL = os.environ.get("BOT_LLM_MODEL", "google/gemma-3-12b-it:free")

# Revenue / payout policy (matches AbhiHub policy).
AI_BASE_SHARE = 0.02          # 2% base to AI models
AI_SHARE_STEP = 0.005         # +0.5% every 2 years
AI_SHARE_CAP = 0.05           # capped at 5%
DEVELOPER_SHARE = 1.0 - AI_BASE_SHARE  # remainder to developer (no college share)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# Set True by run.py --dry-run to guarantee zero network calls.
DRY_RUN = False


def has_llm() -> bool:
    return (not DRY_RUN) and bool(OPENROUTER_API_KEY)


def has_db() -> bool:
    return (not DRY_RUN) and bool(SUPABASE_URL and SUPABASE_KEY)
