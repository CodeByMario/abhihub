"""
services/catalog_sync.py — Syncs live models to the model_catalog table.
Ensures only verified free models are routed.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
import httpx
from supabase import create_client, ClientOptions

log = logging.getLogger(__name__)


def get_db():
    from methods.supabase_helper import init_supabase_admin, init_supabase
    client = init_supabase_admin() or init_supabase()
    if client:
        return client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key, options=ClientOptions(schema="abhihub"))



async def sync_openrouter() -> int:
    """Fetch OpenRouter models, find 0-cost models, and upsert to model_catalog."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        log.warning("[catalog_sync] OPENROUTER_API_KEY missing.")
        return 0

    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=25) as client:
        res = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
        if res.status_code != 200:
            log.error("[catalog_sync] OpenRouter API error %s: %s", res.status_code, res.text)
            return 0
        data = res.json().get("data", [])

    db = get_db()
    if not db:
        log.error("[catalog_sync] Supabase client unavailable.")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    free_records: List[Dict[str, Any]] = []

    for m in data:
        pricing = m.get("pricing", {})
        prompt_cost = float(pricing.get("prompt", 0) or 0)
        completion_cost = float(pricing.get("completion", 0) or 0)
        m_id = m.get("id", "")

        is_free = (prompt_cost == 0 and completion_cost == 0) or m_id.endswith(":free")
        status = "free_verified" if is_free else "paid"

        if is_free:
            free_records.append({
                "id": f"openrouter:{m_id}",
                "provider": "openrouter",
                "model": m_id,
                "status": status,
                "price_in": prompt_cost,
                "price_out": completion_cost,
                "ctx": m.get("context_length", 4096),
                "caps": ["code"] if "code" in m_id.lower() else [],
                "quality_tier": 2,
                "health": 1.0,
                "last_synced_at": now,
                "last_ok_at": now,
                "source": "sync"
            })

    if free_records:
        try:
            db.table("model_catalog").upsert(free_records).execute()
            log.info("[catalog_sync] Synced %d free models from OpenRouter", len(free_records))
            return len(free_records)
        except Exception as exc:
            log.error("[catalog_sync] Failed to upsert model catalog: %s", exc)
            return 0

    return 0


async def sync_all() -> int:
    """Entry point for all provider sync jobs."""
    total = 0
    total += await sync_openrouter()
    return total


_CATALOG_CACHE: Dict[str, Any] = {"ts": 0, "models": []}


def get_active_catalog_models(provider: str = "openrouter", force_fresh: bool = False) -> List[str]:
    """Retrieve verified free models from abhihub.model_catalog with 60s memory caching.
    
    Guarantees only models with status='free_verified' and not currently in cooldown
    are returned.
    """
    import time
    now_ts = time.time()
    if not force_fresh and (now_ts - _CATALOG_CACHE.get("ts", 0) < 60) and _CATALOG_CACHE.get(provider):
        return _CATALOG_CACHE[provider]

    db = get_db()
    if not db:
        return _CATALOG_CACHE.get(provider, [])

    try:
        res = (
            db.table("model_catalog")
            .select("model, quality_tier, health, cooldown_until")
            .eq("provider", provider)
            .eq("status", "free_verified")
            .order("quality_tier", desc=True)
            .order("health", desc=True)
            .execute()
        )
        data = res.data or []
        now_iso = datetime.now(timezone.utc).isoformat()
        models = [
            r["model"]
            for r in data
            if r.get("model") and (not r.get("cooldown_until") or r["cooldown_until"] < now_iso)
        ]
        if models:
            _CATALOG_CACHE[provider] = models
            _CATALOG_CACHE["ts"] = now_ts
        return models or _CATALOG_CACHE.get(provider, [])
    except Exception as exc:
        log.warning("[catalog_sync] get_active_catalog_models error: %s", exc)
        return _CATALOG_CACHE.get(provider, [])

