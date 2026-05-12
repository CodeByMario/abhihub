"""
Centralized Supabase client and shared helpers for the data layer.
"""

import os
import uuid
from dotenv import load_dotenv

load_dotenv()

try:
    from supabase import create_client, Client, ClientOptions
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None
    ClientOptions = None
    print("Warning: supabase-py not installed. Install with: pip install supabase")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_client = None


def get_client():
    """Return (or create) the singleton Supabase client on the abhihub schema."""
    global _client
    if _client is not None:
        return _client

    if not SUPABASE_AVAILABLE:
        print("❌ data.db: supabase-py not available")
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ data.db: SUPABASE_URL or SUPABASE_KEY missing")
        return None

    try:
        _client = create_client(
            SUPABASE_URL,
            SUPABASE_KEY,
            options=ClientOptions(schema="abhihub"),
        )
        print("✅ data.db: Supabase client initialised (abhihub schema)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ data.db: failed to create client – {e}")
        return None

    return _client


# ── Shared helpers ──────────────────────────────────────────────────

def validate_uuid(val) -> bool:
    """Return True if *val* is a valid UUID string."""
    try:
        uuid.UUID(str(val))
        return True
    except Exception:
        return False


def format_file_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable string (e.g. '2.3 MB')."""
    if not size_bytes:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    idx = 0
    size = float(size_bytes)
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.1f} {units[idx]}"
