"""
Firebase Configuration — loaded from environment variables.
All values MUST be provided via .env (or environment) at deploy time.
This file intentionally contains NO hardcoded project secrets so it can
be safely committed to a public repository.

Required env vars (when Firebase features are used):
    FIREBASE_API_KEY
    FIREBASE_AUTH_DOMAIN
    FIREBASE_PROJECT_ID
    FIREBASE_DATABASE_URL
    FIREBASE_STORAGE_BUCKET
    FIREBASE_MESSAGING_SENDER_ID
    FIREBASE_APP_ID
    FIREBASE_MEASUREMENT_ID   (optional — Analytics)

NOTE: The application has migrated to Supabase for auth. Firebase is now
optional / legacy (used only for Firebase Storage if enabled). If you do
not need Firebase Storage, leave these vars unset and the config will
gracefully degrade.
"""

import os
from typing import Optional, Dict


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read an env var, returning None when absent (no hardcoded fallback)."""
    return os.getenv(name, default)


def get_firebase_config() -> Dict[str, Optional[str]]:
    """
    Return the Firebase config dict for the current deployment.

    Each field is read from an env var. When a required var is missing the
    corresponding value is None — callers that need a working Firebase config
    should check for None before initializing.
    """
    return {
        "apiKey": _env("FIREBASE_API_KEY"),
        "authDomain": _env("FIREBASE_AUTH_DOMAIN"),
        "projectId": _env("FIREBASE_PROJECT_ID"),
        "databaseURL": _env("FIREBASE_DATABASE_URL"),
        "storageBucket": _env("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": _env("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": _env("FIREBASE_APP_ID"),
        "measurementId": _env("FIREBASE_MEASUREMENT_ID"),
    }


# Legacy convenience: keep a module-level `firebaseConfig` for any remaining
# code that imports this module and reads `firebaseConfig` directly.
firebaseConfig = get_firebase_config()
