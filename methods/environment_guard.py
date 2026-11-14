"""
AbhiHub Environment & Database Safety Guard
Ensures strict isolation between Production and Staging Supabase instances.
Guarantees zero accidental mutations on production when running staging workflows.
"""
import os
import re

PRODUCTION_PROJECT_REF = "xchqudjccefnykpuzhxd"

def mask_credential(cred: str) -> str:
    """Masks a secret/credential safely, showing only the first 4 and last 4 characters."""
    if not cred:
        return "[NOT SET]"
    if len(cred) <= 8:
        return "***"
    return f"{cred[:4]}...{cred[-4:]}"

def get_active_environment() -> str:
    """Detects active runtime environment from standard environment variables."""
    # Check explicit AGY / staging overrides first
    env = os.getenv("ABHIHUB_ENV", os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development"))).lower()
    return env

def get_supabase_project_ref(url: str = None) -> str:
    """Extracts the Supabase project reference identifier from a project URL."""
    target_url = url or os.getenv("SUPABASE_URL", "")
    match = re.search(r"https://([a-z0-9]+)\.supabase\.co", target_url)
    if match:
        return match.group(1)
    return "[UNKNOWN_REF]"

def is_production_database() -> bool:
    """Returns True if the current SUPABASE_URL matches the production project reference."""
    ref = get_supabase_project_ref()
    return ref == PRODUCTION_PROJECT_REF

def assert_staging_write_allowed(operation_name: str = "write"):
    """
    Raises PermissionError if a script attempts to perform a mutation
    while connected to the production database under a non-production mandate.
    """
    if is_production_database():
        raise PermissionError(
            f"MUTATION BLOCKED: '{operation_name}' targeted production Supabase project "
            f"('{PRODUCTION_PROJECT_REF}'). Staging execution requires an isolated staging project URL."
        )
    return True
